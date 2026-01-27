#!/usr/bin/env python3
"""Evaluate inhaled combination rules against computed 12-week costs.

Reads:
- data/inhaled_drug_master_exact.csv (to know Triple/other categories)
- reports/inhaled_drug_12w_cost_2025-04.csv (computed costs)

Applies rules:
- If any Triple selected -> only Triple remain; others excluded (reason)
- Spiriva (name contains 'スピリーバ') cannot be combined with Triple
- Otherwise ICS/LABA + LAMA allowed; cost sums over active items

Prints active list, excluded list with reasons, and total 12-week cost.
"""
from pathlib import Path
import csv


def load_master(master_path: Path):
    m = {}
    with master_path.open('r', encoding='utf-8') as fh:
        reader = csv.DictReader(fh)
        for r in reader:
            name = r.get('exact_item_name')
            if not name:
                continue
            # skip accidental header-like rows
            if isinstance(name, str) and name.strip().lower() == 'exact_item_name':
                continue
            name = name.strip()
            if name == '':
                continue
            m[name] = r
    return m


def load_costs(cost_csv: Path):
    costs = {}
    with cost_csv.open('r', encoding='utf-8-sig') as fh:
        reader = csv.DictReader(fh)
        for r in reader:
            name = r.get('exact_item_name')
            try:
                cost = float(r.get('cost_12w_yen')) if r.get('cost_12w_yen') not in (None, '') else None
            except Exception:
                cost = None
            costs[name] = {**r, 'cost_12w_yen': cost}
    return costs


def evaluate(master_path: Path, cost_csv: Path):
    master = load_master(master_path)
    costs = load_costs(cost_csv)

    # selected = all items present in costs (found in Excel)
    selected = [name for name in costs.keys()]

    # determine classes for selected
    selected_info = []
    for name in selected:
        m = master.get(name, {})
        cls = m.get('class', '')
        selected_info.append({'name': name, 'class': cls, 'cost_12w': costs[name].get('cost_12w_yen')})

    # rule 1: if any Triple present -> only Triples remain
    triples = [s for s in selected_info if s['class'] == 'Triple']
    excluded = []
    active = []
    if triples:
        active = triples
        for s in selected_info:
            if s['class'] != 'Triple':
                excluded.append({'name': s['name'], 'reason': 'Triple present (Triple overrides other inhalers)'} )
    else:
        # rule 2: Spiriva cannot be combined with Triple (no triple here) -> no-op
        # Spiriva allowed with ICS/LABA
        # all selected remain active
        active = selected_info

    total_cost = sum((a['cost_12w'] or 0) for a in active)

    return {
        'selected': selected_info,
        'active': active,
        'excluded': excluded,
        'total_cost_12w': total_cost,
    }


def main():
    repo = Path('.')
    master = repo / 'data' / 'inhaled_drug_master_exact.csv'
    cost_csv = repo / 'reports' / 'inhaled_drug_12w_cost_2025-04.csv'
    if not cost_csv.exists():
        print('ERROR: cost CSV not found:', cost_csv)
        return
    res = evaluate(master, cost_csv)
    # Print concise summary matching CSV below (we print the detailed ordered summary later)

    # Build and write summary CSV (include master-only items as not found)
    costs = load_costs(cost_csv)  # dict: name -> data
    master_map = load_master(master)

    # Names present in Excel (costs) and in master
    names_in_costs = set(costs.keys())
    names_in_master = []
    # preserve master order by reading the master file again
    with master.open('r', encoding='utf-8') as fh:
        reader = csv.DictReader(fh)
        for r in reader:
            name = r.get('exact_item_name')
            if not name:
                continue
            if isinstance(name, str) and name.strip().lower() == 'exact_item_name':
                continue
            name = name.strip()
            if name == '':
                continue
            names_in_master.append(name)

    names_in_master_set = set(names_in_master)

    # Determine if any Triple is present among items found in Excel
    triples_present = any(
        (master_map.get(n, {}).get('class') == 'Triple') for n in names_in_costs
    )

    # Active names: if triples present -> only Triples (that are in costs), else all items in costs
    if triples_present:
        active_names = set(n for n in names_in_costs if master_map.get(n, {}).get('class') == 'Triple')
    else:
        active_names = set(names_in_costs)

    # Build ordered list: master order first (including master-only), then any cost-only names
    ordered_names = []
    seen_order = set()
    for n in names_in_master:
        if n in seen_order:
            continue
        ordered_names.append(n)
        seen_order.add(n)
    # append any names found in costs but not present in master (cost-only) at the end
    cost_only = [n for n in names_in_costs if n not in names_in_master_set]
    cost_only_sorted = sorted(cost_only)
    ordered_names.extend(cost_only_sorted)

    out_csv = repo / 'reports' / 'inhaled_summary_2025-04.csv'
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ['exact_item_name', 'class', 'price_yen', 'cost_12w_yen', 'selected', 'exclusion_reason']
    with out_csv.open('w', encoding='utf-8-sig', newline='') as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for name in ordered_names:
            # class: prefer master entry, fall back to cost row
            cls = master_map.get(name, {}).get('class', costs.get(name, {}).get('class', ''))
            # price
            price_raw = costs.get(name, {}).get('price_yen') if name in costs else None
            try:
                price = float(price_raw) if price_raw not in (None, '') else None
            except Exception:
                price = None
            # cost12
            cost12 = costs.get(name, {}).get('cost_12w_yen') if name in costs else None
            try:
                cost12_val = float(cost12) if cost12 not in (None, '') else None
            except Exception:
                cost12_val = None

            selected = 'true' if name in active_names else 'false'
            reason = ''
            if name not in names_in_costs:
                reason = 'not found in Excel'
            elif name not in active_names:
                # excluded due to triple presence
                reason = 'Triple present (Triple overrides other inhalers)'

            writer.writerow({
                'exact_item_name': name,
                'class': cls,
                'price_yen': price,
                'cost_12w_yen': cost12_val,
                'selected': selected,
                'exclusion_reason': reason,
            })

    # Print stdout in same order and content as CSV
    print('\nSummary (same order as CSV):')
    for name in ordered_names:
        cls = master_map.get(name, {}).get('class', costs.get(name, {}).get('class', ''))
        price = costs.get(name, {}).get('price_yen') if name in costs else ''
        cost12 = costs.get(name, {}).get('cost_12w_yen') if name in costs else ''
        selected_flag = 'true' if name in active_names else 'false'
        reason = ''
        if name not in names_in_costs:
            reason = 'not found in Excel'
        elif name not in active_names:
            reason = 'Triple present (Triple overrides other inhalers)'
        print(f" - {name} | class={cls} | price_yen={price} | cost_12w_yen={cost12} | selected={selected_flag} | reason={reason}")

    print('\nWROTE:', out_csv)


if __name__ == '__main__':
    main()
