#!/usr/bin/env python3
"""Generate a final inhaled summary CSV with selection/exclusion reasons.

Reads: reports/inhaled_drug_12w_cost_2025-04.csv and data/inhaled_drug_master_exact.csv
Writes: reports/inhaled_summary_2025-04.csv

Columns:
- exact_item_name
- class
- price_yen
- cost_12w_yen
- selected   # true/false
- exclusion_reason

This uses the same combination logic as `evaluate_inhaled_combinations.py`.
"""
from pathlib import Path
import csv


def load_master(master_path: Path):
    m = {}
    with master_path.open('r', encoding='utf-8') as fh:
        reader = csv.DictReader(fh)
        for r in reader:
            m[r['exact_item_name']] = r
    return m


def load_costs(cost_csv: Path):
    rows = []
    with cost_csv.open('r', encoding='utf-8-sig') as fh:
        reader = csv.DictReader(fh)
        for r in reader:
            # normalize numeric fields
            try:
                price = float(r.get('price_yen')) if r.get('price_yen') not in (None, '') else None
            except Exception:
                price = None
            try:
                cost12 = float(r.get('cost_12w_yen')) if r.get('cost_12w_yen') not in (None, '') else None
            except Exception:
                cost12 = None
            rows.append({
                'exact_item_name': r.get('exact_item_name'),
                'class': r.get('class', ''),
                'price_yen': price,
                'cost_12w_yen': cost12,
            })
    return rows


def evaluate_and_build_summary(master_path: Path, cost_csv: Path):
    master = load_master(master_path)
    costs = load_costs(cost_csv)

    # selected: all items present in costs
    selected_info = []
    for r in costs:
        name = r['exact_item_name']
        cls = master.get(name, {}).get('class', r.get('class', ''))
        selected_info.append({
            'name': name,
            'class': cls,
            'price_yen': r.get('price_yen'),
            'cost_12w_yen': r.get('cost_12w_yen'),
        })

    # rule: if any Triple present -> only Triples remain; others excluded
    triples = [s for s in selected_info if s['class'] == 'Triple']
    active_names = set()
    excluded = {}
    if triples:
        active_names = set(t['name'] for t in triples)
        for s in selected_info:
            if s['name'] not in active_names:
                excluded[s['name']] = 'Triple present (Triple overrides other inhalers)'
    else:
        # no triples -> all selected remain active
        active_names = set(s['name'] for s in selected_info)

    # Build summary rows
    summary = []
    for s in selected_info:
        name = s['name']
        is_selected = name in active_names
        reason = '' if is_selected else excluded.get(name, '')
        summary.append({
            'exact_item_name': name,
            'class': s.get('class', ''),
            'price_yen': s.get('price_yen'),
            'cost_12w_yen': s.get('cost_12w_yen'),
            'selected': 'true' if is_selected else 'false',
            'exclusion_reason': reason,
        })

    return summary


def main():
    repo = Path('.')
    master = repo / 'data' / 'inhaled_drug_master_exact.csv'
    cost_csv = repo / 'reports' / 'inhaled_drug_12w_cost_2025-04.csv'
    out_csv = repo / 'reports' / 'inhaled_summary_2025-04.csv'

    if not cost_csv.exists():
        print('ERROR: cost CSV not found:', cost_csv)
        return

    summary = evaluate_and_build_summary(master, cost_csv)

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ['exact_item_name', 'class', 'price_yen', 'cost_12w_yen', 'selected', 'exclusion_reason']
    with out_csv.open('w', encoding='utf-8-sig', newline='') as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for r in summary:
            writer.writerow(r)

    print('WROTE:', out_csv)


if __name__ == '__main__':
    main()
