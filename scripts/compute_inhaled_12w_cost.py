#!/usr/bin/env python3
"""Compute 12-week cost for inhaled drugs.

Reads: reports/inhaled_drug_price_2025-04.csv
Writes: reports/inhaled_drug_12w_cost_2025-04.csv
"""
from pathlib import Path
import csv


def main():
    repo = Path('.')
    in_csv = repo / 'reports' / 'inhaled_drug_price_2025-04.csv'
    out_csv = repo / 'reports' / 'inhaled_drug_12w_cost_2025-04.csv'

    if not in_csv.exists():
        print('ERROR: input CSV not found:', in_csv)
        return

    rows = []
    with in_csv.open('r', encoding='utf-8-sig') as fh:
        reader = csv.DictReader(fh)
        for r in reader:
            name = r.get('exact_item_name')
            try:
                price = float(r.get('price_yen')) if r.get('price_yen') not in (None, '') else None
            except Exception:
                price = None
            try:
                daily = int(r.get('daily_inhalations')) if r.get('daily_inhalations') not in (None, '') else None
            except Exception:
                daily = None
            if price is None or daily is None:
                cost12 = None
            else:
                cost12 = price * daily * 84
            rows.append({
                'exact_item_name': name,
                'price_yen': price,
                'daily_inhalations': daily,
                'cost_12w_yen': cost12,
                'class': r.get('class', ''),
            })

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open('w', encoding='utf-8-sig', newline='') as fh:
        fieldnames = ['exact_item_name', 'price_yen', 'daily_inhalations', 'cost_12w_yen', 'class']
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)

    print('WROTE:', out_csv)


if __name__ == '__main__':
    main()
