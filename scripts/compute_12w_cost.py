#!/usr/bin/env python3
"""Compute 12-week cost from daily prices.

Reads:  reports/oral_drug_daily_price_2025-04.csv
Writes: reports/oral_drug_12w_cost_2025-04.csv

Columns written: drug_name,strength_mg,daily_price_yen,cost_12w_yen,source_excel,sheet,row,unit
"""
from pathlib import Path
import csv


def main():
    repo = Path('.')
    in_csv = repo / 'reports' / 'oral_drug_daily_price_2025-04.csv'
    out_csv = repo / 'reports' / 'oral_drug_12w_cost_2025-04.csv'

    if not in_csv.exists():
        print('ERROR: input CSV not found:', in_csv)
        return

    rows = []
    with in_csv.open('r', encoding='utf-8-sig') as fh:
        reader = csv.DictReader(fh)
        for r in reader:
            try:
                daily = float(r.get('daily_price_yen') or r.get('daily_price') or 0)
            except Exception:
                daily = None
            if daily is None:
                cost12 = None
            else:
                cost12 = daily * 84
            rows.append({
                'drug_name': r.get('drug_name'),
                'strength_mg': r.get('strength_mg'),
                'daily_price_yen': daily,
                'cost_12w_yen': cost12,
                'source_excel': r.get('source_excel', ''),
                'sheet': r.get('sheet', ''),
                'row': r.get('row', ''),
                'unit': r.get('unit', ''),
            })

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open('w', encoding='utf-8-sig', newline='') as fh:
        fieldnames = ['drug_name', 'strength_mg', 'daily_price_yen', 'cost_12w_yen', 'source_excel', 'sheet', 'row', 'unit']
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)

    print('WROTE:', out_csv)


if __name__ == '__main__':
    main()
